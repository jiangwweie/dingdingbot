# Environment Contract

Last updated: 2026-06-01

## Contract

`.env` decides where the system runs.

Carrier / Owner authorization decides what the system may run.

PG profile / safety gates decide how it may run.

Environment variables must not select a live Carrier, symbol, side, cap, or live order authority.

## Minimal Operator-Facing Env

Production and Tokyo pre-live should expose only these groups:

| Group | Variables | Operator responsibility |
| --- | --- | --- |
| Deployment mode | `APP_ENV`, `TRADING_ENV`, `EXCHANGE_TESTNET` | choose deployment class only |
| PostgreSQL | `PG_DATABASE_URL` | server secret / DSN |
| Console auth | `BRC_OPERATOR_USERNAME`, `BRC_OPERATOR_PASSWORD_HASH`, `BRC_OPERATOR_TOTP_SECRET`, `BRC_OPERATOR_SESSION_SECRET`, `BRC_OPERATOR_SESSION_TTL_SECONDS` | server secret values |
| Exchange access | `EXCHANGE_NAME`, `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET` | server secret values; no duplicate Binance aliases |
| Global safety cap | `BRC_EXECUTION_PERMISSION_MAX` | production may be `order_allowed` only as a capability ceiling; live order authority is scoped by Owner authorization and FinalGate |
| Optional LLM | `BRC_LLM_ENABLED`, optional LLM endpoint/model/key | disabled by default |
| Service binding | `BACKEND_PORT`, `API_HOST` | host binding only |

## Variable Classification

| Variable | Read locations | Secret | Execution/order impact | Safe default | Allowed modes | Operator-facing policy |
| --- | --- | --- | --- | --- | --- | --- |
| `APP_ENV` | environment contract validation | no | scopes validation | `development` | dev/testnet/prelive/production | keep |
| `TRADING_ENV` | `runtime_config.py`, `execution_permission.py`, `api_brc_console.py`, scripts | no | live/testnet interpretation | `simulation` or explicit template value | all | keep, but not an authorization |
| `EXCHANGE_TESTNET` | `runtime_config.py`, `api_console_runtime.py`, scripts | no | blocks testnet control endpoints when false | `true` in testnet, `false` in live | all | keep |
| `PG_DATABASE_URL` | `database.py`, `runtime_config.py`, seed scripts, PG repos | yes | selects durable PG state | required | mainline all modes | keep as server secret |
| `CORE_EXECUTION_INTENT_BACKEND` | `database.py`, `runtime_config.py` | no | persistence backend | `postgres` | mainline all modes | fixed to `postgres` |
| `CORE_ORDER_BACKEND` | `database.py`, `runtime_config.py` | no | persistence backend | `postgres` | mainline all modes | fixed to `postgres` |
| `CORE_POSITION_BACKEND` | `database.py`, `runtime_config.py` | no | persistence backend | `postgres` | mainline all modes | fixed to `postgres` |
| `RUNTIME_PROFILE` | `main.py`, `api_console_runtime.py`, scripts | no | selects dev/testnet profile | unset in live/prelive | dev/testnet only | remove from live operator responsibility |
| `BRC_EXECUTION_PERMISSION_MAX` | `execution_permission.py`, `runtime_config.py`, `api_brc_console.py` | no | caps action depth | `read_only` | all | live/prelive may use `order_allowed` only as an official gated execution capability ceiling |
| `RUNTIME_CONTROL_API_ENABLED` | `api_console_runtime.py`, `api_brc_console.py`, tests/scripts | no | exposes mutation/control endpoints | `false` | dev/testnet only by default | remove from production operator responsibility |
| `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED` | `api_console_runtime.py`, `api_brc_console.py`, tests/scripts | no | enables test signal injection | `false` | dev/testnet only | remove from production operator responsibility |
| `EXCHANGE_NAME` | `runtime_config.py` | no | exchange adapter selection | `binance` | all | keep |
| `EXCHANGE_API_KEY` | `runtime_config.py`, testnet scripts | yes | exchange credential | required only where exchange access is enabled | all | canonical key name |
| `EXCHANGE_API_SECRET` | `runtime_config.py`, testnet scripts | yes | exchange credential | required only where exchange access is enabled | all | canonical secret name |
| `BINANCE_API_KEY` | not read by mainline code | yes | none unless future alias support is added | unset | none | do not use in Owner Console mainline |
| `BINANCE_SECRET_KEY` | not read by mainline code | yes | none unless future alias support is added | unset | none | do not use in Owner Console mainline |
| `BRC_OPERATOR_USERNAME` | `operator_auth.py`, smoke scripts | no | console login | required | all | keep |
| `BRC_OPERATOR_PASSWORD_HASH` | `operator_auth.py` | yes | console login | required | all | keep as server secret |
| `BRC_OPERATOR_TOTP_SECRET` | `operator_auth.py` | yes | console login | required | all | keep as server secret |
| `BRC_OPERATOR_SESSION_SECRET` | `operator_auth.py`, smoke scripts | yes | session signing | required | all | keep as server secret |
| `BRC_OPERATOR_SESSION_TTL_SECONDS` | `operator_auth.py` | no | session TTL | `86400` in templates | all | keep |
| `BRC_LLM_ENABLED` | `brc_operator_workflow.py`, `llm_advisory_plane.py`, tests | no | optional assistant feature | `false` | all | keep disabled by default |
| `BRC_LLM_BASE_URL` | `brc_operator_workflow.py`, `llm_advisory_plane.py` | no | optional LLM endpoint | unset | optional | optional |
| `BRC_LLM_API_KEY` | `brc_operator_workflow.py`, `llm_advisory_plane.py` | yes | optional LLM credential | unset | optional | server secret only |
| `BRC_LLM_MODEL` | `brc_operator_workflow.py`, `llm_advisory_plane.py` | no | optional LLM model | unset | optional | optional |
| `FEISHU_WEBHOOK_URL` | `runtime_config.py`, seed tests | yes | notification only | unset | optional | server secret only |

## Guardrails Implemented

- Mainline runtime config rejects `CORE_EXECUTION_INTENT_BACKEND`, `CORE_ORDER_BACKEND`, or `CORE_POSITION_BACKEND` values other than `postgres`.
- Startup PG validation rejects non-PG core backends.
- Production/live validation rejects `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.
- Production/live validation rejects `RUNTIME_CONTROL_API_ENABLED=true`.
- Production/live validation rejects `BRC_EXECUTION_PERMISSION_MAX=execution_intent_allowed`.
- Production/live may use `BRC_EXECUTION_PERMISSION_MAX=order_allowed` only with `RUNTIME_CONTROL_API_ENABLED=false` and `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`; it remains a capability ceiling and not trade authorization.
- Production/live validation rejects `RUNTIME_PROFILE` as a live executable scope selector.

## Runtime Profile Governance

`RUNTIME_PROFILE` is allowed for local/dev/testnet controlled rehearsal.

`RUNTIME_PROFILE` is not allowed to select live Carrier, symbol, side, cap, or live order authority.

Live execution context must resolve from:

- PG-backed Carrier
- PG-backed Owner risk acknowledgement
- PG-backed BoundedLiveTrialAuthorization
- hard safety gates
- authorization scope matched against carrier/profile/symbol/side/cap

Current hard pre-live gap:

- `src/main.py` still has a legacy runtime profile resolution path for startup. The environment contract prevents using `RUNTIME_PROFILE` in production/live, but full live execution context resolution from PG-backed authorization remains a separate pre-live runtime task.

## Execution Permission Governance

`BRC_EXECUTION_PERMISSION_MAX` is a global cap only.

It is not an authorization.

In production/live it must not globally grant generic `execution_intent_allowed`.

In production/live, `order_allowed` means only that the official Owner-bounded
execute endpoint can bind an order-capable gateway after exact Owner
authorization and FinalGate. It does not bind the generic SignalPipeline
executor, start runtime actions, or authorize any symbol/side/size outside the
PG-backed bounded authorization.

Future live trial authority must be scoped to a PG-backed `BoundedLiveTrialAuthorization`.

## Storage Backend Governance

All durable mainline state must use PostgreSQL.

SQLite/local files are allowed only for:

- unit-test fixtures
- temporary developer mocks
- non-authoritative local cache

They must not be the default Owner Console or runtime persistence backend.

## Binance Credential Names

Canonical names:

- `EXCHANGE_API_KEY`
- `EXCHANGE_API_SECRET`

The mainline code does not read `BINANCE_API_KEY` or `BINANCE_SECRET_KEY`.

Do not require operators to duplicate Binance credentials under alias names.

## Templates

- `.env.local.testnet.example`: local controlled testnet rehearsal.
- `.env.tokyo.prelive.example`: Tokyo pre-live deployment, read-only by default.
- `.env.production.example`: production/live Owner Console, read-only by default.
