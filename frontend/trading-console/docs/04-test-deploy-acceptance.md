# Test Deploy Acceptance Plan

## Test Strategy

### Scope

Testing must prove the frontend works as a real browser application, not only as
compiled code. The acceptance path includes local checks, Playwright browser
checks, server deployment, and domain-based Playwright checks.

## Local Verification

| Check | Command Or Tool | Required Evidence |
| --- | --- | --- |
| **Dependency install** | `npm install` | Lockfile and successful install |
| **Type check** | `npm run typecheck` if configured | No TypeScript errors |
| **Lint** | `npm run lint` if configured | No lint failures |
| **Build** | `npm run build` | Production bundle generated |
| **Preview smoke** | Vite preview or static server | App loads locally |

## Playwright Verification

### Required Flows

1. **Login page render**.
2. **Invalid login failure state**.
3. **Valid login with TOTP** when test credentials are available.
4. **Session restoration** through `/api/auth/session`.
5. **Dashboard route** render.
6. **Account risk route** render.
7. **Order ledger route** render.
8. **StrategyGroup route** render.
9. **Exceptions route** render.
10. **Dark/light theme switch** on at least two pages.
11. **Responsive smoke** at desktop and medium viewport widths.

### Artifact Location

All browser artifacts should be stored under:

```text
output/playwright/trading-console/
```

## Review Checklist

| Area | Review Requirement |
| --- | --- |
| **Data boundary** | No migrations or new database tables |
| **Runtime safety** | No page render calls mutation/exchange-write endpoints |
| **Auth** | TOTP is server-side; frontend does not persist secrets |
| **Theme** | Dark and light use semantic tokens |
| **Accessibility** | Inputs have labels, buttons have names, focus states are visible |
| **Responsive layout** | Dense tables remain usable without text overlap |
| **Mock visibility** | Missing fields are registered |

## Deployment Plan

### Default Nginx Static Path

The preferred deployment shape is:

```text
local build -> server static directory -> Nginx domain -> backend API proxy
```

### Required Deployment Inputs

| Input | Status |
| --- | --- |
| **Domain** | `https://jiaoyingpan.cloud/trading-console/` |
| **SSH target** | `tokyo` |
| **Static root** | `/var/www/trading-console` |
| **Release directory** | `/home/ubuntu/brc-deploy/releases/trading-console-frontend-09eecb8e-20260705T175236Z` |
| **Nginx site config** | `/etc/nginx/sites-available/owner-ai-gateway` |
| **Nginx backup** | `/etc/nginx/sites-available/owner-ai-gateway.bak-trading-console-20260705T175236Z` |
| **Rollback tag** | Owner reports tag exists; code changes are isolated on `codex/frontend-trading-console` |

## Rollback Plan

### Required Rollback Evidence

1. Current git tag used as rollback baseline.
2. Previous server static artifact path or release directory.
3. Nginx config unchanged unless explicitly reviewed.
4. Command log for restoring previous release.

## Acceptance Criteria

| Requirement | Evidence |
| --- | --- |
| **Server domain access** | Playwright opens the domain and screenshots login |
| **Authenticated app access** | Playwright completes login or records auth-blocking evidence |
| **Five pages render** | Screenshots for dashboard, account risk, order ledger, strategy groups, exceptions |
| **Theme switching works** | Dark and light screenshots from the server domain |
| **No database table change** | Git diff and search show no migration/table addition |
| **Mock fields documented** | `05-missing-fields.md` contains all mock-backed fields |
| **Deployment reversible** | Rollback tag and server release path recorded |

## Acceptance Evidence

### Completed Checks

| Check | Result | Evidence |
| --- | --- | --- |
| **Production build** | Passed | `npm run build` in `frontend/trading-console` |
| **Domain HTML** | Passed | `https://jiaoyingpan.cloud/trading-console/` returns `200` |
| **Static CSS** | Passed | `/trading-console/assets/index-D7znhW7T.css` returns `200` and `text/css` |
| **Static JS** | Passed | `/trading-console/assets/index-CkTx9aDG.js` returns `200` and `application/javascript` |
| **Unauthenticated session boundary** | Passed | `/api/auth/session` returns `401 Operator login required` |
| **Login page render** | Passed | `output/playwright/trading-console/08-domain-login.png` |
| **Invalid login failure state** | Passed | `output/playwright/trading-console/09-domain-invalid-login.png` |
| **Domain login audit rerun** | Passed | `output/playwright/trading-console/10-domain-login-audit.png` |
| **Domain invalid-login audit rerun** | Passed | `output/playwright/trading-console/11-domain-invalid-login-audit.png` |
| **Domain login theme toggle** | Passed | `output/playwright/trading-console/12-domain-login-theme-toggle-audit.png` |
| **Local five-page render** | Passed | `output/playwright/trading-console/01-dashboard-dark.png` through `05-exceptions-dark.png` |
| **Theme switch** | Passed | `output/playwright/trading-console/06-exceptions-light.png` |
| **Responsive smoke** | Passed | `output/playwright/trading-console/07-order-ledger-900px-dark.png` |

### Remaining Acceptance Constraint

Authenticated domain acceptance for the five protected pages requires a valid
test operator username, password, and current **Google Authenticator TOTP** code.
No frontend or backend bypass was used. Until that credential is available, the
completed server-domain evidence covers static deployment, unauthenticated auth
boundary, login rendering, invalid-login behavior, and login-page theme
switching.
