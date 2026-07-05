# Trading Console Frontend Delivery Process

## Purpose

### Objective

Build the **Trading Console Frontend** in `frontend/trading-console` on branch
`codex/frontend-trading-console`, following a standard software delivery flow:

1. **Design**
2. **Interface contract**
3. **Frontend/backend alignment**
4. **Development and integration**
5. **Review**
6. **Testing**
7. **Commit**
8. **Server deployment**
9. **Domain-based acceptance**

### Boundary

The frontend may compose existing models, APIs, runtime artifacts, and generated
control snapshots. It must not introduce new database tables for this UI.

## Stage Gates

| Stage | Required Output | Exit Criteria |
| --- | --- | --- |
| **Design** | Product design, page IA, theme plan, UX states | Five target pages and login flow are specified before implementation |
| **Interface contract** | API mapping, field-source map, missing-field registry | Every visible page block has a data source class |
| **Frontend/backend alignment** | Alignment notes and accepted constraints | Backend contract is treated as source before UI coding |
| **Development** | React/Vite implementation under `frontend/trading-console` | UI compiles locally and uses adapters instead of table changes |
| **Integration** | Auth/session/API adapters wired to existing endpoints | Login and protected routes work against backend shape |
| **Review** | Self-review notes, risk list, changed-file inventory | No accidental core runtime/database mutation |
| **Testing** | Unit/build checks and Playwright artifacts | Login, theme switch, navigation, and page rendering are verified |
| **Commit** | Focused git commit on `codex/frontend-trading-console` | Only intended files are staged and committed |
| **Deploy** | Server build deployed behind domain | Domain loads the production build |
| **Acceptance** | Playwright screenshots from server domain | Evidence proves real browser acceptance, not local-only success |

## Development Rules

### Data Rules

1. **No new database tables**.
2. **Existing data composition is allowed** through adapters and selectors.
3. **Mock data is a last-mile fallback**, not the default.
4. **Mock fields must be registered** in `05-missing-fields.md`.
5. **UI-only fields** such as color, icon, density, and display priority must stay
   in frontend view models.

### Safety Rules

1. **Read-only console pages** must not call exchange-write or runtime-control
   mutation endpoints.
2. **Login** must use the existing `/api/auth/login` contract and the backend
   **TOTP** verifier.
3. **Owner-facing copy** must use product states and avoid exposing internal
   execution gate names as required Owner decisions.
4. **Deployment** must preserve rollback to the Owner-provided tag.

## Evidence Log

### Verified Repository Facts

| Fact | Evidence |
| --- | --- |
| **Authentication API exists** | `src/interfaces/operator_auth.py` exposes `/api/auth/login`, `/api/auth/logout`, `/api/auth/session` |
| **TOTP support exists** | `src/interfaces/operator_auth.py` uses `BRC_OPERATOR_TOTP_SECRET` and `verify_totp` |
| **Trading console read model exists** | `src/application/readmodels/trading_console.py` defines `TradingConsoleReadModelResponse` |
| **Trading console page APIs exist** | `src/interfaces/api_trading_console.py` exposes `/api/trading-console/dashboard-state`, `/account-risk`, `/order-ledger`, `/recovery-exception-state` |
| **Runtime read APIs exist** | `src/interfaces/api_console_runtime.py` exposes `/api/runtime/overview`, `/portfolio`, `/health`, `/positions`, `/signals`, `/execution/orders`, `/events` |

