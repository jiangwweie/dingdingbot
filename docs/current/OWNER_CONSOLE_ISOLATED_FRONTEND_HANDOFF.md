---
title: OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF
status: FINAL_ISOLATED_EXPLORATION_HANDOFF
authority: docs/current/OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF.md
last_verified: 2026-06-16
---

# Owner Console Isolated Frontend Handoff

## Scope

This handoff freezes the isolated Owner Console exploration in:

```text
/Users/jiangwei/Documents/final-owner-console
```

Current branch:

```text
codex/owner-runtime-console-v1-isolated
```

The isolated exploration phase is complete. Future Owner Console
productization should be owned by the main runtime window. This frontend window
must not continue independently advancing runtime source integration.

## Current Page Entrypoints

### Real Backend Acceptance Entrypoint

Use this entrypoint when checking the current frontend against the local
read-only backend facade.

```bash
cd /Users/jiangwei/Documents/final-owner-console
/opt/homebrew/bin/python3 -m uvicorn src.interfaces.owner_runtime_console_app:app --host 127.0.0.1 --port 8028
```

```bash
cd /Users/jiangwei/Documents/final-owner-console/owner-runtime-console
OWNER_RUNTIME_API_PROXY_TARGET=http://127.0.0.1:8028 VITE_OWNER_USE_MOCK=false npm run dev -- --port 5198
```

Open:

```text
http://127.0.0.1:5198/
```

The frontend source-readiness path is:

```text
GET /api/trading-console/owner-console-source-readiness
```

### Mock State Matrix Entrypoint

This entrypoint is only for visual and state QA.

```bash
cd /Users/jiangwei/Documents/final-owner-console/owner-runtime-console
VITE_OWNER_USE_MOCK=true npm run dev -- --port 5201
```

Open:

```text
http://127.0.0.1:5201/?scenario=normal
http://127.0.0.1:5201/?scenario=stale
http://127.0.0.1:5201/?scenario=processing
http://127.0.0.1:5201/?scenario=paused
http://127.0.0.1:5201/?scenario=intervention
```

## Recommended Files To Carry Forward

These files are useful for the main-window productization pass.

| Path | Carry Forward | Reason |
| --- | --- | --- |
| `owner-runtime-console/src/App.tsx` | yes | Multi-page console shell wiring. |
| `owner-runtime-console/src/console/chrome.tsx` | yes | Sidebar, mobile nav, top safety bar, theme toggle. |
| `owner-runtime-console/src/console/model.ts` | yes | Owner-facing labels, tone mapping, navigation model. |
| `owner-runtime-console/src/console/pages.tsx` | yes | Page composition for 首页, 策略组, 资金, 订单与持仓, 记录, 系统. |
| `owner-runtime-console/src/console/panels.tsx` | yes | Reusable visual panels and StrategyGroup rows. |
| `owner-runtime-console/src/api/ownerSourceReadiness.ts` | yes | Source-readiness adapter for the main runtime API. |
| `owner-runtime-console/src/api/ownerProductProjection.ts` | partial | Keep adapter switch and loading semantics; do not preserve legacy endpoint as the primary production path. |
| `owner-runtime-console/src/types.ts` | yes | Current frontend contract types. |
| `owner-runtime-console/scripts/visual-qa.mjs` | yes | Hard visual QA gate and screenshot ledger generator. |
| `owner-runtime-console/scripts/state-smoke.mjs` | yes | Owner-state matrix smoke. |
| `owner-runtime-console/scripts/real-backend-smoke.mjs` | yes | Real-backend connected/unavailable smoke. |
| `owner-runtime-console/package.json` | yes | Required scripts: `build`, `smoke`, `smoke:states`, `smoke:real`, `visual:qa`. |
| `docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md` | yes | UI hard gate SSOT. |
| `docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` | yes | Product projection and source-health semantics. |
| `docs/current/OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF.md` | yes | Backend source-readiness handoff history. |
| `docs/current/OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF.md` | yes | Final isolated-exploration freeze note. |
| `tests/unit/test_owner_runtime_console_readmodel.py` | partial | Keep source-readiness contract assertions; move into main backend test ownership. |
| `tests/unit/test_owner_runtime_product_projection.py` | partial | Keep compatibility assertions only if the old product projection facade remains temporarily supported. |

## Files Not Recommended For Direct Carry Forward

These files or code paths were useful during isolation but should not become
the production source of truth.

| Path / Area | Do Not Carry Forward As-Is | Reason |
| --- | --- | --- |
| `owner-runtime-console/src/data.ts` mock scenario builders | production code | Keep only as QA fixtures or storybook-like examples. |
| `src/interfaces/owner_runtime_console_app.py` | production backend | Temporary lightweight local FastAPI app for isolated frontend validation. |
| `src/interfaces/api_owner_runtime_console.py` local wrapper behavior | production source of truth | Useful as compatibility facade, but main runtime should own the real API implementation. |
| `src/application/owner_runtime_product_projection.py` legacy projection path | primary frontend target | The new product path should prefer source readiness from `/api/trading-console/owner-console-source-readiness`. |
| `owner-runtime-console/artifacts/*` | source code | Generated screenshots and ledgers; keep as review evidence only. |
| `owner-runtime-console/dist/*` | source code | Build output. |
| URL query `?scenario=...` | production runtime behavior | QA-only scenario injection. |
| `VITE_OWNER_USE_MOCK=true` | production runtime behavior | QA-only mock mode. |

## Current Tests And Results

Last verified on 2026-06-16 in the isolated worktree.

| Command | Result | Notes |
| --- | --- | --- |
| `npm run build` | passed | TypeScript and Vite production build passed. |
| `npm run smoke` | passed | Normal mock load smoke passed. |
| `npm run smoke:states` | passed | 7 scenarios passed: normal, processing, paused, intervention, stale, empty, error. |
| `npm run smoke:real` | passed | Connected local read-only backend and unavailable backend branches passed. |
| `npm run visual:qa` | passed | normal/stale, dark/light, six pages, five viewport classes passed; ledger generated. |
| `/opt/homebrew/bin/pytest tests/unit/test_owner_runtime_product_projection.py tests/unit/test_owner_runtime_console_readmodel.py -q` | passed | 21 tests passed. |
| `/opt/homebrew/bin/python3 -m py_compile src/interfaces/api_owner_runtime_console.py src/interfaces/owner_runtime_console_app.py` | passed | Local backend facade syntax passed. |

Visual QA evidence:

```text
/Users/jiangwei/Documents/final-owner-console/owner-runtime-console/artifacts/visual-qa/visual-ledger.md
```

Real-backend smoke evidence:

```text
/Users/jiangwei/Documents/final-owner-console/owner-runtime-console/artifacts/real-backend-smoke/
```

## Current SourceHealth Field Assumptions

The frontend currently assumes this source status enum:

```text
ready
ready_empty
ready_nonempty
degraded
unavailable
```

The frontend currently consumes these `source_health` fields:

| Field | Frontend Key | Expected Status Meaning | Owner Label Rule |
| --- | --- | --- | --- |
| `strategy_catalog` | `catalog` | StrategyGroup catalog is readable. | StrategyGroups remain visible. |
| `runtime_source` | `runtime` | Runtime overlay is readable, degraded, or unavailable. | Does not hide StrategyGroups by itself. |
| `watcher` | `watcher` | Watcher observation status. | Drives high-level freshness and observation language. |
| `live_facts` | `liveFacts` | Combined account/order/position/protection fact freshness. | Helps determine whether business data is usable. |
| `funds` | `accountFunds` | Account/fund source readiness. | `资金正常` or `资金状态暂不可用`. |
| `orders` | `orders` | Local order source readiness. | `暂无订单` is normal when `ready_empty`. |
| `positions` | `positions` | Local position source readiness. | `暂无持仓` is normal when `ready_empty`. |
| `protection` | `protection` | Protection state readiness. | `保护正常` or one compressed unavailable sentence. |
| `reconciliation` | `reconciliation` | Reconciliation detail readiness. | Current main-window update expects `ready` and `对账正常`. |
| `operation_audit` | `operationAudit` | Operation audit detail readiness. | Current main-window update expects `ready_empty` and `暂无审计动作`. |

The latest main-window source readiness update should map as:

| Field | Expected Status | Expected Owner Summary |
| --- | --- | --- |
| `source_health.reconciliation.status` | `ready` | `owner_summary.reconciliation = 对账正常` |
| `source_health.operation_audit.status` | `ready_empty` | `owner_summary.operation_audit = 暂无审计动作` |

Business-data usability is intentionally stricter than backend connectivity.
The frontend treats the backend as connected when the API responds, but treats
business data as usable only when live facts, funds, orders, positions, and
protection are readable or explicitly ready-empty.

## Handoff Boundary

The isolated frontend branch is a product and UI exploration snapshot.

The main runtime window should take over:

- real API ownership;
- Tokyo packet/API compatibility;
- source-readiness field finalization;
- production routing;
- deployment integration.

The isolated frontend window should stop:

- adding new runtime source probes;
- changing live/runtime source semantics independently;
- expanding mock scenarios as if they were backend truth;
- maintaining a parallel backend path.

## Safety Boundary

This snapshot does not authorize:

- real order placement;
- exchange write;
- credential or secret mutation;
- live profile expansion;
- order-sizing changes;
- FinalGate bypass;
- Operation Layer bypass.
