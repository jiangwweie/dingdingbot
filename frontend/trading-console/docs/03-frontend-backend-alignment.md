# Frontend Backend Alignment Record

## Alignment Status

### Current Status

This document is the alignment ledger for the **Trading Console Frontend**. It
must be updated before implementation moves into development and again before
deployment.

## Decisions

| Decision | Status | Rationale |
| --- | --- | --- |
| **New frontend partition**: `frontend/trading-console` | Accepted | Keeps console work isolated from Python runtime source |
| **New branch**: `codex/frontend-trading-console` | Accepted | Focused branch for review and rollback discipline |
| **No new database tables** | Accepted | UI composes existing models and read models |
| **Use existing auth API** | Accepted | Backend already supports username, password, and TOTP |
| **Use page-level read models first** | Accepted | `/api/trading-console/*` already wraps runtime data and no-action guarantees |
| **Use mock only for gaps** | Accepted | Preserves development speed while keeping gaps explicit |
| **Deploy as static frontend behind Nginx by default** | Accepted and verified | Deployed at `https://jiaoyingpan.cloud/trading-console/` with `/api/` proxied to backend |

## Backend Contracts To Verify During Integration

| Contract | Verification Method | Required Result |
| --- | --- | --- |
| **`/api/auth/session`** | Browser request with and without cookie | Returns authenticated state or 401/unauthenticated response consistently |
| **`/api/auth/login`** | Test operator account with valid TOTP | Issues `brc_operator_session` cookie |
| **`/api/trading-console/dashboard-state`** | Authenticated GET | Returns `TradingConsoleReadModelResponse` |
| **`/api/trading-console/account-risk`** | Authenticated GET | Returns risk data or structured unavailable entries |
| **`/api/trading-console/order-ledger`** | Authenticated GET with limit | Returns ledger data or structured unavailable entries |
| **`/api/trading-console/strategygroup-runtime-pilot-status`** | Authenticated GET | Returns StrategyGroup runtime projection |
| **`/api/trading-console/recovery-exception-state`** | Authenticated GET | Returns exception/recovery projection |

## Frontend Contracts To Provide

| Contract | Required Frontend Artifact |
| --- | --- |
| **Auth adapter** | `login`, `logout`, `getSession` functions |
| **API client** | Cookie-aware fetch wrapper with 401/503 handling |
| **Page adapters** | `toDashboardViewModel`, `toAccountRiskViewModel`, `toOrderLedgerViewModel`, `toStrategyGroupsViewModel`, `toExceptionsViewModel` |
| **Mock registry** | Development mocks annotated by source and replacement target |
| **Theme provider** | Dark/light persistent mode with semantic tokens |
| **Route guard** | Protected routes redirect unauthenticated users to `/login` |

## Open Alignment Items

| Item | Current Handling | Final Resolution Needed Before Deployment |
| --- | --- | --- |
| **Server domain** | `https://jiaoyingpan.cloud/trading-console/` | Verified by curl and Playwright domain load |
| **SSH/deploy target** | `tokyo` | Static frontend release copied to `/var/www/trading-console` |
| **Production auth env** | Backend expects env vars | Login boundary verified by `/api/auth/session` 401 and invalid login failure; valid credential acceptance still requires a test operator credential |
| **Chart history density** | Use existing runtime data where available | Mock only missing sparkline/equity history with registry entry |
| **Light-mode target** | Derived from semantic tokens | Verify screenshots after implementation |

## Freeze Rule

Development may start only after:

1. Product design exists.
2. Interface contract exists.
3. Missing-field registry exists.
4. Frontend/backend alignment ledger records current accepted assumptions.
