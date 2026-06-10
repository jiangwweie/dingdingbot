# Tokyo Runtime Governance Deployment Acceptance - 2026-06-10

Status: ACCEPTED_WITH_AUTHENTICATED_CONSOLE_CHECK_PENDING

This record captures the deployed Tokyo state after the runtime-governance
backend deployment and the follow-up Trading Console static frontend refresh.

## Scope

Deployed:

- Runtime governance backend release.
- Alembic migrations from 044 to 064.
- Trading Console static frontend build.
- Post-deploy read-only verification.

Not deployed / not authorized:

- No real exchange order.
- No executable `ExecutionIntent` submit.
- No `OrderLifecycle` call.
- No strategy self-authorization.
- No withdrawal or transfer behavior.
- No live runtime trading activation.

## Public Entry

- Public URL: `http://43.133.176.150/`
- Public listener: nginx on port `80`
- Backend listener: `127.0.0.1:18080`
- Nginx API proxy: `/api/* -> http://127.0.0.1:18080`
- No public `5174` listener was observed.

## Backend Release

- Deployed release path:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ae9b209e-20260610T061250Z`
- Current symlink:
  `/home/ubuntu/brc-deploy/app/current -> /home/ubuntu/brc-deploy/releases/brc-runtime-governance-ae9b209e-20260610T061250Z`
- Deployed backend SHA:
  `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- Local deployed tag:
  `deploy/tokyo-runtime-governance-20260610-ae9b209e`
- Backend service:
  `brc-owner-console-backend.service`
- Service state:
  `active`
- Health response:
  `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`

Note: local release branch HEAD is currently `531491b5`, which only fixes the
post-deploy verifier expectation for authenticated endpoints. The actual
deployed backend release remains `ae9b209e`.

## Database

- Alembic version after deploy: `064`
- Latest migration file:
  `2026-06-10-064_add_runtime_profile_proposal_snapshot.py`
- Remote backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-ae9b209e-20260610T061250Z.pgdump`
- Backup size observed: `291964` bytes

Deployment repaired several real environment/deploy issues before acceptance:

- Remote environment uses `PG_DATABASE_URL`, not `DATABASE_URL`.
- Host did not have `pg_dump`; backup now falls back to the Postgres container.
- Alembic now prefers `PG_DATABASE_URL` / `DATABASE_URL` over the local sqlite default.
- Promotion-confirmation check constraint names were shortened for PostgreSQL's
  63-character identifier limit.

## Frontend Static Build

The first public check showed the previous 2026-06-08 frontend assets. The
current branch frontend was then built locally and synced to nginx static root.

Remote frontend files now observed:

- `/var/www/brc-owner-console/index.html`
- `/var/www/brc-owner-console/assets/index-C-PmEdZd.js`
- `/var/www/brc-owner-console/assets/index-DVwpkJDn.css`
- `/var/www/brc-owner-console/server.cjs`
- `/var/www/brc-owner-console/server.cjs.map`

The public HTML now references:

- `assets/index-C-PmEdZd.js`
- `assets/index-DVwpkJDn.css`

Old AppleDouble `._*` files introduced by the local tar archive were removed.

## Verification

Read-only post-deploy verifier:

- Status: `postdeploy_acceptance_passed`
- Release identity: `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- Migration count: `64`
- Latest migration: `2026-06-10-064_add_runtime_profile_proposal_snapshot.py`
- Warning: `release_identity_from_manifest_without_git_status`

Public smoke:

- `GET /` returned `200`.
- `GET /api/health` returned `200`.
- `GET /api/trading-console/strategy-runtimes?limit=1` returned `401`.
- `POST /api/trading-console/operations-cockpit` returned `405`.

Playwright public UI smoke:

- Page opened at `http://43.133.176.150/login`.
- Page title: `Trading Console`.
- Login form rendered.
- Dark mode rendered.
- Light/dark mode toggle worked.
- Screenshot artifacts:
  - `output/playwright/tokyo-public-login-after-frontend-20260610.png`
  - `output/playwright/tokyo-public-login-light-20260610.png`

The only browser console error observed during anonymous smoke was the expected
`401 Unauthorized` for `/api/auth/session`, which causes the login page to be
shown.

## Authenticated Console Check Pending

The following checks require Owner login / TOTP handoff and were not completed
by Codex in this pass:

- Login succeeds with Operator account.
- Dashboard / Runtime / Strategy / Review / Capital pages render authenticated
  read-model data.
- Runtime strategy pages show promotion gate / safety readiness without false
  live-ready claims.
- Strategy observation and shadow planning surfaces render without frontend-only
  fake-ready states.
- Dark/light mode remains usable after login.
- Authenticated API reads return `200` for expected `GET /api/trading-console/*`
  endpoints.
- Non-allowed generic POST remains blocked.

## Deployment Method Note

This deployment used the existing artifact/symlink release layout plus a manual
frontend static sync. The next deploy-system cleanup should move Tokyo toward a
git-based release/tag flow:

```text
release branch / deploy tag
-> tokyo git fetch
-> checkout exact tag/SHA
-> build frontend on server or from CI artifact
-> alembic upgrade head
-> systemctl restart backend
-> nginx static root update
-> postdeploy verify
```

That cleanup is deployment tooling work only and should not grant trading
authority.
