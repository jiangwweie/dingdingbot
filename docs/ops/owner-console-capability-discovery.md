# Owner Console Frontend/API Capability Discovery

**Date:** 2026-06-03
**Mode:** Read-only — no code changes, no migrations, no mutations

> [!IMPORTANT]
> 2026-06-08 scope note:
> This document is a historical read-only capability discovery snapshot. Its
> old dashboard/action-hiding findings are superseded as product direction by
> `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`.
> Current Console direction is Owner-facing bounded-live operations through
> official authorization, `FinalGate`, Operation Layer, protection, and Review.

---

## 1. Current Frontend Page Inventory

| Route | Component | Purpose | Data Displayed | API Calls | Primary Actions | Env Relevance |
|-------|-----------|---------|-----------------|-----------|-----------------|---------------|
| `/login` | `Login` | Auth gate | Username, password, TOTP | `POST /api/auth/login` | Submit login | LIVE — TOTP required |
| `/home` | `HomeV2` | Owner workbench dashboard | Priority action, 5-step flow progress, candidate/execution/readiness cards, blockers, risks | 20+ endpoints via `useConsoleData()` — `readiness`, `accountFacts`, `mi001SolReadiness`, `strategyGroupReviewability`, `ownerTrialFlowCurrent`, `bnbLiveExecutionBridgeDryRun`, `secondCarrierExpansion`, `multiCarrierBudgetAuthorizationCurrent`, `listStrategyFamilies`, `listAdmissionDecisions`, `listTrialBindings`, `currentCampaign`, `reviewPacket`, `evidence`, `listOperations` | Navigate to `/trial-confirmation`, navigate to `/strategy-candidates` | LIVE-RELEVANT — reads real account facts |
| `/trial-confirmation` | `TrialConfirmationV2` | Full risk acknowledgment + authorization + live trial execution trigger | Authorization state, carrier details, risk checkboxes, metadata status, final gate read model, execution plan preview, testnet verification | All `useConsoleData()` + `POST /api/brc/owner-trial-flow/risk-acknowledgement` + `POST /api/brc/owner-trial-flow/authorization-draft` + `POST /api/brc/owner-trial-flow/authorization-draft/{id}/activate-live-authorization` + `POST /api/brc/owner-trial-flow/authorizations/{id}/execute` | Risk acknowledgment checkboxes → create draft → activate authorization → execute (gated) | LIVE-CRITICAL — execution trigger could place real orders |
| `/strategy-candidates` | `StrategyCandidatesV2` | Market view input + candidate selection | Coin, regime, direction, risk mode, system candidates, strategy type shelf | `useConsoleData()` | Generate candidates (local), confirm selection → navigate to `/trial-confirmation` | READ-ONLY — local state only |
| `/strategy-groups` | `StrategyCandidatesV2` | Alias for strategy-candidates | Same as above | Same | Same | READ-ONLY |
| `/intents` | `IntentsV2` | Execution plan / intent display | Pending candidate, authorization status, risk acknowledgment count, 5-step chain status | `useConsoleData()` | Navigation only | READ-ONLY |
| `/account-orders` | `AccountOrdersV2` | Account facts, positions, orders | Carrier context, BNB positions, BNB open orders, reconciliation status, source, equity, margin, P&L, abnormal exposure | `brcApi.accountFacts()` | None — read-only | LIVE-RELEVANT — reads real exchange data |
| `/analysis` | `AnalysisV2` | Post-trial review | Pre-trial status, risk disclosure, conclusion, BNB testnet evidence grid | `useConsoleData()` | None — read-only | READ-ONLY |
| `/trace` | `TraceV2` | Timeline trace | Candidate formation → risk acceptance → PG registration → review → current blocker | `useConsoleData()` | Click-to-expand nodes | READ-ONLY |

**Retired routes (24):** All redirect to `/home`. Files still exist for: `CommandCenter`, `MarketsOrders`, `RuntimeControl`, `RiskAccount`, `FixedTestnetRehearsal`, `LlmCopilot`, `StrategyFamilies`, `StrategyPlaybook`, `Review`, `AuditTrail`, `Dashboard`, `Guide`, `Workflow`, `Operator`, `Ledger`, `DeveloperDetail`.

---

## 2. Backend API Inventory

### 2.1 Auth (`/api/auth`)

| Method | Path | Purpose | Reads | Mutates PG | Touches Exchange | Safety Guards |
|--------|------|---------|-------|------------|------------------|---------------|
| POST | `/api/auth/login` | Login with username/password/TOTP | Env vars | No | No | PBKDF2-SHA256, TOTP 30s window, HMAC cookie |
| POST | `/api/auth/logout` | Clear session | None | No | No | Cookie deletion |
| GET | `/api/auth/session` | Validate session | Env vars | No | No | HMAC signature, expiry, username |

### 2.2 BRC Console — Read Endpoints (`/api/brc`)

| Method | Path | Purpose | Reads | Mutates PG | Touches Exchange |
|--------|------|---------|-------|------------|------------------|
| GET | `/api/brc/readiness` | Readiness dashboard | Runtime, BRC service, config, GKS, guard, position/order repos, exchange, account equity | No | No |
| GET | `/api/brc/readiness/mi001-sol` | MI001-SOL readiness | Runtime, GKS, guard, env | No | No |
| GET | `/api/brc/readiness/mi001-bnb/trial-gap` | BNB trial readiness gap | Derived | No | No |
| GET | `/api/brc/readiness/startup-guard/preflight-arm` | Startup guard arm preflight | Guard, env | No | No |
| GET | `/api/brc/strategy-groups/reviewability` | Strategy group reviewability | Derived | No | No |
| GET | `/api/brc/strategy-groups/live-readonly-observation/v1` | Live market observation | Market sources | No | No |
| GET | `/api/brc/strategy-groups/observation-cases/v1` | Observation case queue | PG observation + forward review repos | No | No |
| GET | `/api/brc/strategy-trial-architecture/bnb-first-carrier` | Architecture governance | Derived | No | No |
| GET | `/api/brc/strategy-trial-architecture/second-carrier-expansion` | Second carrier expansion | Derived | No | No |
| GET | `/api/brc/owner-trial-flow/current` | Current owner trial flow | PG owner trial flow repo | No | No |
| GET | `/api/brc/budget-authorizations/current` | Multi-carrier budget auth | PG budget repo | No | No |
| GET | `/api/brc/owner-trial-flow/authorization-draft/{id}` | Authorization draft detail | PG | No | No |
| GET | `/api/brc/markets-orders` | Markets + orders overview | Position/order repos, exchange, equity | No | No |
| GET | `/api/brc/account-facts` | Account facts | Position/order repos, exchange, equity | No | No |
| GET | `/api/brc/audit-trail` | Audit trail | BRC service, operation repo | No | No |
| GET | `/api/brc/operations/capabilities` | Operation capabilities | Derived | No | No |
| GET | `/api/brc/operations` | Operation list | Operation service | No | No |
| GET | `/api/brc/operations/{id}` | Operation detail | Operation service | No | No |

### 2.3 BRC Console — Write Endpoints (`/api/brc`)

| Method | Path | Purpose | Mutates PG | Touches Exchange | Safety Guards |
|--------|------|---------|------------|------------------|---------------|
| POST | `/api/brc/strategy-groups/live-readonly-observation/v1/run-once` | Trigger observation | Yes (observation records) | No | Operator session |
| POST | `/api/brc/budget-authorizations/foundation` | Create budget authorization | Yes | No | Operator session |
| POST | `/api/brc/owner-trial-flow/risk-acknowledgement` | Record risk acknowledgment | Yes | No | Operator session |
| POST | `/api/brc/owner-trial-flow/authorization-draft` | Create authorization draft | Yes | No | Operator session |
| POST | `/api/brc/owner-trial-flow/authorization-draft/{id}/activate-live-authorization` | Activate live authorization | Yes | No | Operator session |
| POST | `/api/brc/owner-trial-flow/live-execution-bridge/dry-run` | Execution bridge dry-run | No | No | Operator session |
| POST | `/api/brc/owner-trial-flow/authorizations/{id}/execute` | **EXECUTE LIVE TRIAL** | Yes (intent + order) | **YES** | Operator session + final hard gate + TRADING_ENV=live + EXCHANGE_TESTNET=false + RUNTIME_CONTROL_API_ENABLED=false |
| POST | `/api/brc/ask` | Investigator AI query | No | No | Operator session |
| POST | `/api/brc/operations/preflight` | Operation preflight | No | No | Operator session |
| POST | `/api/brc/operations/confirm` | Confirm operation | Yes (operation results) | Conditional | Operator session + confirmation phrase |
| POST | `/api/brc/operations/{id}/cancel` | Cancel operation | Yes | No | Operator session |
| POST | `/api/brc/operator/strategy-families` | Create strategy family | Yes | No | Operator session |
| POST | `/api/brc/operator/evidence-packets` | Create evidence packet | Yes | No | Operator session |
| POST | `/api/brc/operator/owner-market-regime-inputs` | Create regime input | Yes | No | Operator session |
| POST | `/api/brc/operator/admission-requests` | Create admission request | Yes | No | Operator session |
| POST | `/api/brc/operator/owner-risk-acceptances` | Create risk acceptance | Yes | No | Operator session + confirmation phrase |

### 2.4 Runtime Console (`/api/runtime`)

| Method | Path | Purpose | Mutates PG | Touches Exchange | Safety Guards |
|--------|------|---------|------------|------------------|---------------|
| GET | `/api/runtime/safety` | Runtime safety state | No | No | Operator session |
| GET | `/api/runtime/overview` | Runtime overview | No | No | None (read-only) |
| GET | `/api/runtime/portfolio` | Portfolio context | No | No | None (read-only) |
| GET | `/api/runtime/health` | Runtime health | No | No | None (read-only) |
| GET | `/api/runtime/positions` | Position list | No | No | None (read-only) |
| GET | `/api/runtime/signals` | Signal list | No | No | None (read-only) |
| GET | `/api/runtime/attempts` | Attempt list | No | No | None (read-only) |
| GET | `/api/runtime/execution/orders` | Order list | No | No | None (read-only) |
| GET | `/api/runtime/execution/intents` | Execution intent list | No | No | None (read-only) |
| GET | `/api/runtime/events` | Event list | No | No | None (read-only) |
| GET | `/api/runtime/control/global-kill-switch` | GKS status | No | No | Localhost only |
| POST | `/api/runtime/control/global-kill-switch` | Toggle GKS | Yes (PG) | No | Localhost + env flag |
| GET | `/api/runtime/control/startup-trading-guard` | Guard status | No | No | Localhost only |
| POST | `/api/runtime/control/startup-trading-guard/arm` | Arm guard | In-memory | No | Localhost + env flag |
| POST | `/api/runtime/control/startup-trading-guard/block` | Block guard | In-memory | No | Localhost + env flag |
| GET | `/api/runtime/control/campaign-state` | Campaign state | No | No | Localhost only |
| POST | `/api/runtime/control/campaign-state` | Update campaign state | Yes (PG) | No | Localhost + env flag |
| POST | `/api/runtime/test/smoke/execute-controlled-entry` | Controlled entry | Yes | **YES** | 8 gates: env + localhost + testnet + profile + once-per-session + guard + GKS + circuit breaker |
| POST | `/api/runtime/test/smoke/execute-controlled-close` | Controlled close | Yes | **YES** | Same gates |
| POST | `/api/runtime/test/brc/carriers/{id}/execute-controlled-entry` | Carrier controlled entry | Yes | **YES** | Carrier scope + all gates |
| POST | `/api/runtime/test/brc/carriers/{id}/execute-controlled-close` | Carrier controlled close | Yes | **YES** | Carrier scope + all gates |

### 2.5 Config API (`/api/v1/config`)

| Method | Path | Purpose | Mutates PG | Touches Exchange | Safety Guards |
|--------|------|---------|------------|------------------|---------------|
| GET | `/api/v1/config` | Config summary | No | No | None |
| GET | `/api/v1/config/risk` | Risk config | No | No | None |
| PUT | `/api/v1/config/risk` | Update risk config | Yes | No | Admin permission |
| GET | `/api/v1/config/system` | System config | No | No | None |
| PUT | `/api/v1/config/system` | Update system config | Yes | No | Admin permission |
| GET/POST/PUT/DELETE | `/api/v1/config/strategies` | Strategy CRUD | Yes (write ops) | No | Admin permission |
| GET/POST/PUT/DELETE | `/api/v1/config/symbols` | Symbol CRUD | Yes (write ops) | No | Admin permission |
| GET/POST/PUT/DELETE | `/api/v1/config/notifications` | Notification CRUD | Yes (write ops) | No | Admin permission |
| POST | `/api/v1/config/import/confirm` | Import config | Yes (all) | No | Admin + preview token |
| POST | `/api/v1/config/snapshots/{id}/activate` | Activate snapshot | Yes | No | Admin permission |
| GET/PUT | `/api/v1/config/exchange` | Exchange config | Yes (PUT) | Hot-reload reconnect | Admin permission |

---

## 3. Real Account Facts Support

| Capability | Status | Details |
|------------|--------|---------|
| Environment/profile detection | **SUPPORTED** | `readiness()` → `environment_boundary`, `RuntimeSafetyResponse` includes `testnet`, `profile`, `environment_mode` |
| Account equity / wallet balance / margin | **SUPPORTED** | `accountFacts()` → `account_summary.equity`, `available_balance`, `margin`, `unrealized_pnl`; backed by `BinanceAccountService.fetch_balance()` |
| Exchange positions | **SUPPORTED** | `accountFacts()` → `bnb_positions[]`; `positions()` endpoint; backed by `ExchangeGateway.fetch_positions()` |
| Exchange open orders | **SUPPORTED** | `accountFacts()` → `bnb_open_orders[]`; `execution/orders` endpoint; backed by `ExchangeGateway.fetch_open_orders()` |
| PG orders | **SUPPORTED** | `execution/orders` → reads from `OrderRepository`; `markets-orders` → combined PG + exchange |
| PG vs exchange reconciliation | **SUPPORTED** | `accountFacts()` includes `reconciliation_status`, `source`, `truth_level`; `Reconciliation` service compares PG ↔ exchange, marks ghost/orphan orders |
| Data freshness timestamp | **PARTIAL** | `accountFacts()` includes `source` field indicating data origin; no explicit `last_updated` timestamp on account snapshot |
| Stale/unknown state | **PARTIAL** | `AccountRiskAssessment` has `UNKNOWN` state; `account_facts` may return empty/error states; no explicit staleness timeout displayed |
| GKS status | **SUPPORTED** | `readiness()` includes GKS state; `GET /api/runtime/control/global-kill-switch` returns `active`, `reason`, `updated_at` |
| Startup guard status | **SUPPORTED** | `readiness()` includes guard state; `GET /api/runtime/control/startup-trading-guard` returns `armed`, `blocked` |

---

## 4. Authorization Lifecycle Support

| Capability | Status | Details |
|------------|--------|---------|
| Owner risk acknowledgment | **SUPPORTED** | `POST /api/brc/owner-trial-flow/risk-acknowledgement` — creates `OwnerRiskAcknowledgement` in PG |
| Authorization draft | **SUPPORTED** | `POST /api/brc/owner-trial-flow/authorization-draft` — creates `BoundedLiveTrialAuthorizationDraft` in PG |
| Bounded live trial authorization | **SUPPORTED** | `POST /api/brc/owner-trial-flow/authorization-draft/{id}/activate-live-authorization` — creates `BoundedLiveTrialAuthorization` in PG |
| Unconsumed authorization | **SUPPORTED** | `GET /api/brc/owner-trial-flow/current` — returns current authorization state; `ownerTrialFlowCurrent` in frontend |
| Consumed authorization | **SUPPORTED** | Authorization state transitions tracked in PG; flow step shows consumed status |
| Expired authorization | **UNCLEAR** | No explicit TTL or expiry mechanism found in authorization models |
| Cancellation / voiding | **UNCLEAR** | No explicit cancel/void endpoint for authorizations found |
| Active authorization lookup | **SUPPORTED** | `GET /api/brc/owner-trial-flow/current` + `GET /api/brc/owner-trial-flow/authorization-draft/{id}` |
| Authorization scope: carrier | **SUPPORTED** | Authorization draft includes `carrier_id` |
| Authorization scope: symbol | **SUPPORTED** | Carrier includes symbol |
| Authorization scope: side | **SUPPORTED** | Carrier includes direction/side |
| Authorization scope: cap | **SUPPORTED** | Authorization includes `max_notional` cap |
| Authorization scope: max notional | **SUPPORTED** | Explicit in authorization model |
| Authorization scope: profile | **PARTIAL** | Authorization references carrier profile but no independent profile scope field |
| Authorization scope: environment | **PARTIAL** | Final gate checks `TRADING_ENV=live` + `EXCHANGE_TESTNET=false` at execution time, not stored in authorization |

---

## 5. Execution/Protection Lifecycle Support

| Capability | Status | Details |
|------------|--------|---------|
| Final hard gate preview | **SUPPORTED** | `POST /api/brc/owner-trial-flow/live-execution-bridge/dry-run` — dry-run gate check; frontend displays final gate read model (startup guard, GKS, account facts, position, order, persistence) |
| Execution plan preview | **SUPPORTED** | `bnbLiveExecutionBridgeDryRun()` returns execution plan preview; frontend displays on trial-confirmation page |
| Execution intent creation | **SUPPORTED** | Execution orchestrator creates `ExecutionIntent` in PG on `execute` call |
| Live execution trigger | **SUPPORTED** | `POST /api/brc/owner-trial-flow/authorizations/{id}/execute` — gated behind TRADING_ENV=live + EXCHANGE_TESTNET=false + RUNTIME_CONTROL_API_ENABLED=false |
| Entry order status | **SUPPORTED** | `execution/orders` endpoint; order lifecycle service tracks state transitions |
| Fill-based protection plan | **SUPPORTED** | Protection planner creates TP/SL orders on fill; `execute` endpoint includes protection plan |
| TP order status | **SUPPORTED** | Protection orders tracked in order repo; reconciliation checks protection health |
| SL order/algo status | **SUPPORTED** | Same as TP — protection orders in order repo |
| Partial protection failure | **PARTIAL** | `list_protection_health_blocks()` checks for protection health issues; no explicit partial-failure recovery endpoint |
| Recovery flat | **PARTIAL** | Recovery repo exists for recovery records; `execute_controlled_close` provides flatten capability (testnet only); no production recovery endpoint |
| Review/result | **SUPPORTED** | `reviewPacket()` returns post-trial review; `evidence()` returns evidence summary; `analysis` page displays results |

---

## 6. Recovery/Cleanup Support

| Capability | Status | Details |
|------------|--------|---------|
| Refresh account facts | **SUPPORTED** | `GET /api/brc/account-facts` — fresh read on each call; `BinanceAccountService.fetch_balance()` calls exchange directly |
| Cancel stale open orders | **PARTIAL** | `Reconciliation` service identifies and cancels ghost orders; no standalone "cancel stale orders" endpoint exposed to frontend |
| Flatten scoped position | **PARTIAL** | `execute_controlled_close` available on testnet carriers; no production position-flatten endpoint |
| Retry missing protection order | **NOT_FOUND** | No explicit endpoint to retry a missing TP/SL order |
| Mark manual review required | **PARTIAL** | Review decisions API exists (`POST /api/runtime/test/brc/review-decisions`); no explicit "mark manual review" action |
| Reconcile PG vs exchange | **SUPPORTED** | `Reconciliation` service runs automatically; `accountFacts()` includes reconciliation status |
| Block new authorization when unresolved exposure exists | **SUPPORTED** | Final hard gate checks `bnb_positions`, `bnb_open_orders`, and `no_active_positions` before allowing execution |

---

## 7. Page-to-API Gap Matrix

### Real Environment Dashboard

| Aspect | Status |
|--------|--------|
| Existing APIs | `readiness()`, `accountFacts()`, `runtime/safety`, `runtime/overview`, `runtime/health` |
| Missing APIs | None — current APIs cover dashboard needs |
| Unavailable fields | Data freshness timestamp, stale-state timeout |
| Actions to hide | Historical finding — superseded by current product model; actions require official backend wiring and safety gates |
| Safety concerns | Account facts may be stale if exchange is unreachable |

### Account & Orders

| Aspect | Status |
|--------|--------|
| Existing APIs | `accountFacts()`, `markets-orders`, `execution/orders`, `positions()` |
| Missing APIs | Standalone "cancel order" endpoint; "flatten position" endpoint (production) |
| Unavailable fields | Order fill timestamp, average fill price per TP/SL |
| Actions to hide | Cancel order, flatten position — no safe production endpoints |
| Safety concerns | Displayed positions/orders may be stale; reconciliation grace period (10s) |

### Current Trial / Authorization

| Aspect | Status |
|--------|--------|
| Existing APIs | `ownerTrialFlowCurrent`, `authorization-draft`, `activate-live-authorization` |
| Missing APIs | Authorization expiry/TTL; authorization cancel/void |
| Unavailable fields | Authorization expiry time, void reason |
| Actions to hide | None for current flow; cancel authorization would need new backend |
| Safety concerns | Consumed authorization may still appear if flow state is inconsistent |

### Execution Control

| Aspect | Status |
|--------|--------|
| Existing APIs | `live-execution-bridge/dry-run`, `authorizations/{id}/execute` |
| Missing APIs | Order cancel endpoint; order modify endpoint; partial-close endpoint |
| Unavailable fields | Execution latency, order fill progress, slippage |
| Actions to hide | Cancel/modify/close — no production endpoints |
| Safety concerns | Execute button is the **only** live-exchange-touching action; gated but extremely high consequence |

### Recovery / Exception Handling

| Aspect | Status |
|--------|--------|
| Existing APIs | `Reconciliation` service (internal); `list_protection_health_blocks()` (internal) |
| Missing APIs | **No frontend-facing recovery endpoints** — cancel stale orders, flatten position, retry protection, mark review required |
| Unavailable fields | Recovery history, exception queue |
| Actions to hide | Historical finding — show unavailable actions unless official recovery endpoint and gates exist |
| Safety concerns | **Critical gap** — if protection order fails, no UI path to recover |

### Review

| Aspect | Status |
|--------|--------|
| Existing APIs | `reviewPacket()`, `evidence()`, `review-decisions` |
| Missing APIs | None significant |
| Unavailable fields | Review timeline, decision history |
| Actions to hide | None |
| Safety concerns | None |

### Technical Audit

| Aspect | Status |
|--------|--------|
| Existing APIs | `audit-trail`, `trace` page data, `runtime/events`, `runtime/signals` |
| Missing APIs | None significant |
| Unavailable fields | Log aggregation, error trace |
| Actions to hide | None |
| Safety concerns | None |

---

## 8. Safety Findings

### 8.1 Dangerous or Ambiguous UI

| Finding | Severity | Detail |
|---------|----------|--------|
| Execute button on `/trial-confirmation` | **HIGH** | "执行这一次小额实盘试验" calls `executeOwnerTrialAuthorization()` which creates real ExecutionIntent and places real exchange order. Currently gated, but button label does not clearly convey "this will place a real BNB order on your exchange account" |
| Metadata-only buttons may confuse | MEDIUM | "后端记录风险确认并生成授权草案" and "确认授权这一次真实小额试验" write to PG but are labeled as "metadata-only" internally. User may not understand these are safe vs. the execute button |

### 8.2 API Mutation/Exchange-Touch Visibility

| Finding | Severity | Detail |
|---------|----------|--------|
| `/api/brc/owner-trial-flow/authorizations/{id}/execute` | **HIGH** | Only endpoint that can place real exchange orders. Safety guards are internal (final hard gate) but not visible in API response — caller cannot see which gates passed or failed before execution |
| `/api/brc/operations/confirm` | MEDIUM | Generic operation confirm can conditionally touch exchange depending on operation type. Safety depends on operation preflight, not self-evident from API schema |
| Retired endpoints still exist in code | LOW | `CommandCenter`, `Operator` etc. have exchange-touching buttons but routes redirect to `/home`. Risk if routes are re-enabled without audit |

### 8.3 Testnet/Live Ambiguity

| Finding | Severity | Detail |
|---------|----------|--------|
| Environment indicators are strong | LOW | Amber capsule "实盘只读 . 记录意图 . 禁止下单", page badges "环境可见 / 证据优先 / 无交易入口", `live_ready: false` type literal on all responses — well-designed |
| `web/` prototype has no env indication | LOW | Static prototype has no environment awareness but also no API integration — cannot affect state |
| `mockApi.ts` exists alongside real API client | LOW | Mock API file exists in production frontend but is not wired to any active route |

### 8.4 Mock Data Mixed with Real Data

| Finding | Severity | Detail |
|---------|----------|--------|
| `sample_data` fallback in frontend | MEDIUM | `DataSource` includes `'sample_data'` — if backend is unreachable, frontend may display sample data without clear indication it is not real |
| `mockApi.ts` not wired | LOW | Mock API not used in any active route |

### 8.5 Stale Account Facts Risk

| Finding | Severity | Detail |
|---------|----------|--------|
| No explicit freshness timestamp | MEDIUM | `accountFacts()` does not include a `last_updated` timestamp; if exchange is unreachable, stale data may be displayed without staleness indicator |
| Reconciliation grace period | LOW | 10-second grace period before confirming mismatches is reasonable but not exposed to frontend |

### 8.6 Consumed Authorization Shown as Actionable

| Finding | Severity | Detail |
|---------|----------|--------|
| Authorization state transitions not fully visible | MEDIUM | `ownerTrialFlowCurrent` returns flow state, but frontend must derive whether authorization is consumed vs. actionable from flow step field — no explicit `is_consumed` / `is_actionable` flag |

### 8.7 Old Trial Data Polluting Current State

| Finding | Severity | Detail |
|---------|----------|--------|
| `ownerTrialFlowCurrent` scoped to carrier | LOW | Flow is carrier-scoped; switching carriers should not carry state. However, no explicit "reset" or "clear previous trial" endpoint exists |
| Campaign state persistence | LOW | Campaign state is PG-persisted; old campaigns may have residual state. `currentCampaign()` returns latest |

---

## Summary

### SUPPORTED NOW

- Account facts (equity, balance, margin, P&L)
- Exchange positions (via exchange gateway)
- Exchange open orders (via exchange gateway)
- PG orders (via order repository)
- PG vs exchange reconciliation
- GKS status read/toggle (localhost only)
- Startup guard status read/arm/block (localhost only)
- Risk acknowledgment → authorization draft → live authorization (full metadata chain)
- Final hard gate preview (dry-run)
- Execution intent creation + order placement (gated behind TRADING_ENV=live + multiple safety checks)
- Entry order status tracking
- Fill-based protection plan (TP/SL order creation)
- TP/SL order status
- Review packet + evidence summary
- Audit trail + timeline trace
- Operation preflight/confirm/cancel framework
- Strategy family admission pipeline

### PARTIAL / NEEDS API GAP FILL

- Data freshness timestamp (no `last_updated` on account facts)
- Stale-state detection (no explicit staleness timeout)
- Authorization expiry/TTL (no expiry mechanism)
- Authorization cancel/void (no endpoint)
- Cancel stale open orders (reconciliation does it internally; no frontend endpoint)
- Flatten scoped position (testnet only; no production endpoint)
- Partial protection failure recovery (health blocks detected but no recovery endpoint)
- Mark manual review required (review decisions exist; no explicit action)
- Execution gate visibility (gates are internal; frontend cannot see pass/fail per gate)
- Stale data indicator on UI

### NOT SUPPORTED

- Retry missing protection order (no endpoint)
- Production position flatten (testnet-only via controlled close)
- Standalone order cancel endpoint (frontend-facing)
- Order modify endpoint
- Partial close endpoint
- Authorization expiry enforcement
- Authorization void/cancel
- Recovery exception queue UI

### SAFETY RISKS

1. **Execute button is extremely high consequence** — the only path to real exchange orders. Gate checks are internal and not visible to the caller before execution.
2. **No frontend-facing recovery endpoints** — if a protection order fails or stale orders exist, there is no UI path to recover. All recovery is internal-only.
3. **Sample data fallback** — if backend is unreachable, frontend may display sample data. Staleness risk.
4. **No authorization expiry** — an activated authorization could remain valid indefinitely if the execution never completes.

### QUESTIONS FOR PRODUCT OWNER

1. Should the execute button label explicitly state "this will place a real [SYMBOL] order on your [EXCHANGE] account"?
2. Should account facts include a `last_updated` timestamp and staleness indicator?
3. Should authorizations have an explicit TTL (e.g., 1 hour) after activation?
4. Should there be a frontend-facing "cancel authorization" endpoint?
5. Should recovery endpoints (cancel stale orders, flatten position, retry protection) be exposed to the frontend, or remain internal-only?
6. Should the final hard gate response include per-gate pass/fail detail visible to the frontend?
7. Should the `sample_data` fallback be removed or made more visually distinct?
8. Is there a product need for a dedicated Recovery / Exception Handling page, or should recovery remain a backend-only concern?
