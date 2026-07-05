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
| **Domain** | Pending server verification |
| **SSH target** | Pending server verification |
| **Static root** | Pending server verification |
| **Nginx site config** | Pending server verification |
| **Rollback tag** | Owner reports tag exists; exact tag pending verification |

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

