# Trading Console Interface Contract

## Contract Position

### Known Facts

The backend already exposes **authentication**, **runtime read models**, and
**trading-console read models**. The frontend must consume those existing
contracts before considering any backend extension.

### Analysis

The first frontend version should treat `/api/trading-console/*` as the primary
page-level read source, and use `/api/runtime/*` as supplemental operational
read models when the page-level source lacks chart/table detail.

## Authentication API

| Endpoint | Method | Request | Response | Frontend Use |
| --- | --- | --- | --- | --- |
| **`/api/auth/login`** | `POST` | `{ username, password, totp_code }` | `SessionResponse` | Login with Google Authenticator style code |
| **`/api/auth/session`** | `GET` | Cookie session | `SessionResponse` | Restore session on app load |
| **`/api/auth/logout`** | `POST` | Cookie session | `SessionResponse` | End session |

### Session Response Shape

The frontend expects:

```ts
type SessionResponse = {
  authenticated: boolean
  username?: string | null
  expires_at_ms?: number | null
  current_stage: string
  next_recommended_step: string
  global_planning_stage: string
  live_ready: boolean
}
```

### Authentication Notes

1. **TOTP** is server-validated with the backend secret.
2. The frontend must not generate, display, or store the **TOTP secret**.
3. Login failures should use neutral copy and avoid revealing which factor
   failed.

## Shared Trading Console Envelope

### Response Type

Most page-level endpoints return:

```ts
type TradingConsoleReadModelResponse = {
  read_model: string
  generated_at_ms: number
  source: string
  freshness_status: string
  warnings: Array<Record<string, unknown>>
  blockers: Array<Record<string, unknown>>
  unavailable: Array<Record<string, unknown>>
  data: Record<string, unknown>
  no_action_guarantee: {
    places_order: boolean
    cancels_order: boolean
    replaces_order: boolean
    flattens_position: boolean
    retries_protection: boolean
    starts_runtime: boolean
    grants_auto_execution: boolean
    mutates_pg: boolean
  }
  live_ready: boolean
}
```

### Frontend Rule

The adapter must preserve `warnings`, `blockers`, `unavailable`,
`freshness_status`, and `no_action_guarantee` for diagnostics and review even
when the visual card displays a simplified product state.

## Page Endpoint Mapping

| Page | Primary Endpoint | Supplemental Endpoints | Source Class |
| --- | --- | --- | --- |
| **仪表盘** | `/api/trading-console/dashboard-state` | `/api/runtime/overview`, `/api/runtime/portfolio`, `/api/runtime/health`, `/api/runtime/events` | direct + composed |
| **账户风险** | `/api/trading-console/account-risk` | `/api/runtime/portfolio`, `/api/runtime/positions`, `/api/runtime/health` | direct + derived |
| **订单台账** | `/api/trading-console/order-ledger` | `/api/runtime/execution/orders`, `/api/runtime/execution/intents`, `/api/runtime/events` | direct + composed |
| **策略组** | `/api/trading-console/strategygroup-runtime-pilot-status` | `/api/trading-console/strategy-group-live-facts-readiness`, `/api/trading-console/runtime-signal-watcher-status`, `/api/trading-console/signal-marker-feed` | artifact-backed + composed |
| **异常信息** | `/api/trading-console/recovery-exception-state` | `/api/trading-console/protection-health`, `/api/runtime/health`, `/api/runtime/events` | direct + composed |

## Data Source Classes

| Class | Definition | Allowed Use |
| --- | --- | --- |
| **direct** | Backend field directly matches UI need | Render with formatting only |
| **composed** | Multiple backend objects combine into one UI block | Adapter-level aggregation |
| **derived** | UI field can be calculated from existing data | Selector-level calculation |
| **artifact-backed** | Runtime report or control snapshot provides current projection | Use only according to project authority order |
| **mock-required** | No existing model/API/artifact supports the field | Mock plus registry entry |
| **ui-only** | Visual metadata unrelated to business facts | Local component/view-model field |

## Initial Field Mapping

| UI Area | Field Examples | Candidate Existing Source | Source Class |
| --- | --- | --- | --- |
| **Top status bar** | system health, account health, execution permission | `/api/runtime/health`, `/api/trading-console/execution-control-state` | composed |
| **KPI cards** | active strategies, open orders, PnL, risk metrics | `/api/trading-console/dashboard-state`, `/api/runtime/portfolio` | direct + derived |
| **Order table** | order id, symbol, side, type, status, qty, price | `/api/runtime/execution/orders`, `/api/trading-console/order-ledger` | direct |
| **Order timeline** | signal event, candidate promotion, action evidence, result | `/api/trading-console/audit-chain`, `/api/runtime/events` | composed |
| **StrategyGroup cards** | group id, state, direction, symbols, fresh event | `/api/trading-console/strategygroup-runtime-pilot-status`, `/strategy-group-live-facts-readiness` | artifact-backed |
| **Candidate pool** | opportunity, trigger time, symbol, strategy, strength | `/api/trading-console/signal-marker-feed`, watcher status | composed |
| **Exception list** | priority, title, target, detected time, state | `/api/trading-console/recovery-exception-state`, `/api/runtime/events` | direct + composed |
| **Charts** | equity curve, sparkline, distribution donut | `/api/runtime/portfolio`, aggregated runtime snapshots, mock fallback | derived + mock-required |

## Verified Data Keys

### Page-Level Read Models

| Endpoint | Verified `data` Keys | Frontend Adapter Use |
| --- | --- | --- |
| **`/api/trading-console/dashboard-state`** | `environment`, `guards`, `account_snapshot_summary`, `positions`, `orders`, `consistency`, `authorization`, `freshness` | Dashboard KPIs, top status bar, runtime summary, order/position summaries |
| **`/api/trading-console/account-risk`** | `risk_state`, `account`, `positions`, `open_orders`, `margin_facts`, `protection_ownership`, `freshness` | Account equity, margin, risk state, protection coverage, position risk distribution |
| **`/api/trading-console/order-ledger`** | `orders`, `groups`, `classification_counts`, `unavailable_fields` | Order table, order status distribution, ledger unavailable-field indicators |
| **`/api/trading-console/protection-health`** | Protection summary object | Protection checklist and coverage cards |
| **`/api/trading-console/recovery-exception-state`** | `recovery_tasks`, `recovery_task_counts`, `mismatches`, `manual_action_required`, `read_only_actions`, `operational_drift`, `deferred_actions` | Exception list, recovery workbench, reconciliation/protection health cards |
| **`/api/trading-console/execution-control-state`** | `hard_gate`, `execution_preview`, `deferred_execute_endpoint` | Execution permission display in top status bar without exposing action authority |
| **`/api/trading-console/signal-marker-feed`** | `markers`, `chart_adapter` | Candidate pool feed and signal/order markers |
| **`/api/trading-console/strategygroup-runtime-pilot-status`** | StrategyGroup runtime pilot artifact | StrategyGroup cards, selected detail, owner-state projection, candidate readiness |

### StrategyGroup Composite Sources

The **StrategyGroup** page should treat
`/api/trading-console/strategygroup-runtime-pilot-status` as its main source.
That endpoint composes:

1. **`strategy_group_handoff_intake`**
2. **`strategy_group_live_facts_readiness`**
3. **`runtime_signal_watcher_status`**

The frontend must show simplified product states while preserving raw blocker
and warning evidence for developer diagnostics.

## API Client Requirements

### Request Behavior

1. Send credentials with same-origin cookie support.
2. Redirect to `/login` on **401**.
3. Show unavailable state on **503** without crashing the app shell.
4. Never call mutation endpoints during page render.

### Adapter Behavior

1. Convert backend shape to page-specific **ViewModel**.
2. Attach field-source metadata during development.
3. Keep unknown backend fields available in diagnostics.
4. Use mock only after direct/composed/derived/artifact-backed sources fail.
