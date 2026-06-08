# Trading Console Frontend Read-Model Gate 2 Acceptance Report

Date: 2026-06-04

> [!IMPORTANT]
> 2026-06-08 scope note:
> This report verifies a Gate 2 read-model frontend. It must not be generalized
> into a product-wide read-only boundary. Current product authority is
> `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`.

Verdict: PASS_WITH_CONSTRAINT

## Scope

Reviewed and updated the AI Studio Trading Console frontend under `trading-console/`.

Pages checked:

- Dashboard
- Account Risk
- Order Ledger
- Protection Health
- Carrier Shelf
- Authorization State
- Execution Control
- Recovery Exception State
- Review State
- Audit Chain
- Signal Marker Feed

Backend contract source:

- `docs/ops/trading-console-read-model-api-contract-v0.1.md`
- `src/interfaces/api_trading_console.py`
- `src/application/readmodels/trading_console.py`
- `tests/unit/test_trading_console_readmodels.py`

## Acceptance Summary

| Area | Result | Evidence |
| --- | --- | --- |
| Local mock/fixture API disabled | PASS | `trading-console/server.ts` now proxies `GET /api/trading-console/*` to `TRADING_CONSOLE_API_BASE`; it no longer creates read-model fixture payloads. |
| Frontend API namespace | PASS | Code scan found no Trading Console truth-source calls to `/api/brc/*`, `/api/runtime/*`, or `/api/dev/testnet/brc/*`. |
| Proxy action safety | PASS | Proxy rejects non-GET `/api/trading-console/*` requests with 405. |
| Shared envelope rendering | PASS | Pages render `freshness_status`, `warnings`, `blockers`, `unavailable`, and no-action guarantee anomalies through shared UI components. |
| `not_available` handling | PASS | Object and array forms of `unavailable_fields` are normalized and rendered; values are not estimated. |
| Deferred/future action slots | PASS | `deferred_actions`, `future_action_slots`, and `deferred_execute_endpoint` render through disabled buttons only. |
| Backend contract field binding | PASS | Frontend binds dashboard/account/order/execution/review fields to backend contract shapes instead of previous fixture shapes. |
| Build/typecheck | PASS | `npm run lint` and `npm run build` passed. |
| Backend read-model safety tests | PASS | `tests/unit/test_trading_console_readmodels.py`: 10 passed. |
| Authenticated frontend proxy GET verification | PASS_WITH_CONSTRAINT | A temporary `src.interfaces.api:app` process was started without trading runtime. Operator login succeeded after setting test auth env after module import. All `/api/trading-console/*` endpoints returned HTTP 200 through `localhost:3000` proxy. One backend degraded-path field gap remains: `authorization-state.data.future_action_slots` missing when owner trial flow service is unavailable. |
| Browser page rendering | PASS | Headless Chrome DevTools Protocol loaded all Trading Console routes with an operator session cookie. Every route rendered a React root, used title `Trading Console`, showed no read-model API error panel, and emitted no console/runtime errors. |
| Local Chrome browser acceptance | PASS | A real local Chrome window was opened with `--remote-debugging-port=9223`; an operator session cookie was injected; all routes rendered successfully with no read-model API error panel, no console/runtime errors, and no enabled dangerous action buttons. |

## Page Contract Classification

| Page | Result | Notes |
| --- | --- | --- |
| Dashboard | PASS | Uses `account_snapshot_summary.total_balance`, array counts for `orders.pg_open`, `orders.exchange_open`, and `orders.open_intents`, and explicit `authorization.status/is_actionable/blocking_reason`. |
| Account Risk | PASS | Uses `account.total_balance`, `available_balance`, `positions`, `open_orders`, `margin_facts`, and `protection_ownership`; unknown/degraded risk is not shown as clean. |
| Order Ledger | PASS | Uses `orders`, `groups`, `classification_counts`, and object/array `unavailable_fields`; no fee/funding/slippage fabrication. |
| Protection Health | PASS | Added read-only page for `protection-health`; displays status, counts, findings, actions exposed, and disabled deferred slots. |
| Carrier Shelf | PASS | Uses `carrier-availability`, preserves BNB-first scope, and flags `sample_data_policy` if not `not_used`. |
| Authorization State | PASS_WITH_CONSTRAINT | Uses `authorization-state`; `future_action_slots` supports object, array, or missing forms and remains disabled. Backend degraded path currently omits `future_action_slots`; tracked in backend dependency sync v0.2. |
| Execution Control | PASS | Uses `hard_gate.gates`, `execution_preview`, and disabled `deferred_execute_endpoint`; no execute API exposed. |
| Recovery Exception State | PASS | Uses `recovery_tasks`, `mismatches`, `manual_action_required`, and disabled `deferred_actions`; unavailable/degraded states are not displayed as clean. |
| Review State | PASS | Uses `reviews`, `filled_order_facts`, `positions`, and object/array `unavailable_fields`; cost fields remain not available. |
| Audit Chain | PASS | Uses `/api/trading-console/audit-chain` without malformed query suffix; raw payload policy is displayed. |
| Signal Marker Feed | PASS_WITH_CONSTRAINT | Uses backend marker feed and chart adapter status; chart rendering remains post-Gate2 scope. |

## API Call Exceptions

Allowed calls present:

- `/api/trading-console/dashboard-state`
- `/api/trading-console/account-risk?include_exchange=true`
- `/api/trading-console/order-ledger`
- `/api/trading-console/protection-health`
- `/api/trading-console/carrier-availability`
- `/api/trading-console/authorization-state`
- `/api/trading-console/execution-control-state`
- `/api/trading-console/recovery-exception-state`
- `/api/trading-console/review-state`
- `/api/trading-console/audit-chain`
- `/api/trading-console/signal-marker-feed`

Forbidden calls found: none.

Unknown calls found: none.

## State Rendering Exceptions

No frontend code-level exception remains for the required Gate 2 states:

- `freshness_status`
- `warnings`
- `blockers`
- `unavailable`
- `not_available`
- `deferred_actions`
- `future_action_slots`
- `deferred_execute_endpoint`

Runtime constraint: authenticated proxy GET verification and headless browser rendering completed. The remaining contract exception is backend-side: degraded `authorization-state` response omits `future_action_slots`.

## Mock / Sample Data Findings

Previous local API fixtures were removed from `trading-console/server.ts`.

Remaining `sample data` text appears only as product policy copy stating that sample data is not accepted as Trading Console truth source.

## Verification Commands

Passed:

```bash
cd trading-console && npm ci
cd trading-console && npm run lint
cd trading-console && npm run build
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py
git diff --check
```

Additional safe probes:

```bash
curl http://127.0.0.1:8000/api/trading-console/dashboard-state
```

Result: no service was listening on `127.0.0.1:8000` before the temporary test process.

Temporary API process:

```bash
python3 -m uvicorn src.interfaces.api:app --host 127.0.0.1 --port 8000
```

Safety note: this did not start `src.main` and did not initialize trading runtime.

Authenticated frontend-proxy verification:

```bash
POST http://127.0.0.1:8000/api/auth/login
GET  http://127.0.0.1:3000/api/trading-console/{endpoint}
```

Result:

- Login succeeded with temporary local operator credentials.
- All Trading Console read-model endpoints returned HTTP 200 through the frontend proxy.
- Every returned `no_action_guarantee` flag was `false`.
- Every returned envelope had `live_ready=false`.
- `authorization-state` degraded path missed `data.future_action_slots`.

Headless browser route verification:

```bash
Google Chrome --headless=new --remote-debugging-port=9222
```

Routes verified:

- `/`
- `/account`
- `/ledger`
- `/protection`
- `/carrier`
- `/authorization`
- `/execution`
- `/recovery`
- `/review`
- `/audit`
- `/signals`

Result:

- Each route rendered one React root child.
- Each route returned document title `Trading Console`.
- No route displayed `Read Model API 读取失败`.
- No route emitted console/runtime errors.

Local Chrome browser acceptance:

```bash
Google Chrome --remote-debugging-port=9223 --user-data-dir=/tmp/tc-real-browser-profile http://127.0.0.1:3000/
```

Routes verified in the local browser:

| Route | Expected page text | Result |
| --- | --- | --- |
| `/` | `真实风险总览` | PASS |
| `/account` | `账户总览` | PASS |
| `/ledger` | `订单台账` | PASS |
| `/protection` | `保护健康` | PASS |
| `/carrier` | `Carrier Shelf` | PASS |
| `/authorization` | `有界实盘授权` | PASS |
| `/execution` | `实盘执行控制` | PASS |
| `/recovery` | `异常恢复` | PASS |
| `/review` | `实盘复盘` | PASS |
| `/audit` | `技术审计` | PASS |
| `/signals` | `信号图表预留` | PASS |

Observed in local Chrome:

- Document title was `Trading Console` on every route.
- React root rendered on every route.
- No route displayed `Read Model API 读取失败`.
- Every route showed the expected page heading.
- Every route showed `not_live_connected` / unavailable state where returned by the backend.
- Enabled dangerous action buttons count was `0` on every route.
- Disabled action slots remained disabled on Protection, Execution, Recovery, and Audit pages.
- Console/runtime errors count was `0` for all verified routes.

## Safety Proof

No live order, cancel, replace, flatten, retry protection, runtime start, auto-execution grant, exchange write, PG migration, credential change, Tokyo deploy, push, or real-funds action was performed.

The frontend proxy forwards only `GET /api/trading-console/*` and rejects non-GET requests under that namespace.

## Backend Dependency Sync v0.2

Generated:

- `docs/ops/trading-console-backend-dependency-sync-v0.2.md`

Reason:

- `GET /api/trading-console/authorization-state` omits `future_action_slots` in the degraded/no-owner-service path. The frontend handles this safely, but strict backend contract completeness requires the field in all branches.

## Final Decision

Frontend code is ready for Gate 2 handoff with the following constraint:

1. Backend should add `future_action_slots` to the degraded `authorization-state` path for strict contract completeness.
2. Signal chart rendering remains post-Gate2; the page only validates backend marker feed shape.

Final result: PASS_WITH_CONSTRAINT.
